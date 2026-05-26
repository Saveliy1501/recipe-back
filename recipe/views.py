from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter
from django.db.models import Count
from collections import Counter
import json

from .models import Recipe, RecipeLike
from .serializers import RecipeLikeSerializer, RecipeSerializer
from .permissions import IsAuthorOrReadOnly
from django.db.models import Q


@extend_schema(
    parameters=[
        OpenApiParameter(
            name='search',
            type=str,
            location='query',
            description='Поиск по названию, описанию или ингредиентам'
        ),
        OpenApiParameter(
            name='category__name',
            type=str,
            location='query',
            description='Фильтр по названию категории'
        ),
        OpenApiParameter(
            name='author__username',
            type=str,
            location='query',
            description='Фильтр по имени автора'
        ),
    ]
)
class RecipeListAPIView(generics.ListAPIView):
    serializer_class = RecipeSerializer
    permission_classes = (AllowAny,)
    filterset_fields = ('category__name', 'author__username')
    
    def get_queryset(self):
        queryset = Recipe.objects.annotate(
            likes_count=Count('recipelike')
        ).select_related('author', 'category')
        
        # Поиск
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(desc__icontains=search) |
                Q(ingredients__icontains=search)
            )
        
        # Сортировка
        ordering = self.request.query_params.get('ordering', None)
        if ordering:
            # Преобразуем имена полей для сортировки по аннотированным полям
            if ordering == 'total_number_of_likes':
                queryset = queryset.order_by('likes_count')
            elif ordering == '-total_number_of_likes':
                queryset = queryset.order_by('-likes_count')
            elif ordering == 'cook_time':
                queryset = queryset.order_by('cook_time')
            elif ordering == '-cook_time':
                queryset = queryset.order_by('-cook_time')
            else:
                queryset = queryset.order_by(ordering)
        
        return queryset


class RecipeCreateAPIView(generics.CreateAPIView):
    """
    Create: a recipe
    """
    queryset = Recipe.objects.all()
    serializer_class = RecipeSerializer
    permission_classes = (IsAuthenticated,)

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)


class RecipeAPIView(generics.RetrieveUpdateDestroyAPIView):
    """
    Get, Update, Delete a recipe
    """
    queryset = Recipe.objects.all()
    serializer_class = RecipeSerializer
    permission_classes = (IsAuthorOrReadOnly,)


class RecipeLikeAPIView(generics.CreateAPIView):
    """
    Like, Dislike a recipe
    """
    serializer_class = RecipeLikeSerializer
    permission_classes = (IsAuthenticated,)

    def post(self, request, pk):
        recipe = get_object_or_404(Recipe, id=self.kwargs['pk'])
        new_like, created = RecipeLike.objects.get_or_create(
            user=request.user, recipe=recipe)
        if created:
            new_like.save()
            return Response(status=status.HTTP_201_CREATED)
        return Response(status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        recipe = get_object_or_404(Recipe, id=self.kwargs['pk'])
        like = RecipeLike.objects.filter(user=request.user, recipe=recipe)
        if like.exists():
            like.delete()
            return Response(status=status.HTTP_200_OK)
        return Response(status=status.HTTP_400_BAD_REQUEST)

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

class RecipeRecommendationsAPIView(generics.GenericAPIView):
    """
    Get personalized recipe recommendations based on user's saved recipes.
    If user has less than 5 saved recipes, return top liked recipes.
    If user has 5 or more saved recipes, return recipes with similar ingredients.
    """
    permission_classes = (IsAuthenticated,)
    serializer_class = RecipeSerializer

    def get(self, request, *args, **kwargs):
        user = request.user
        saved_recipes = user.profile.bookmarks.all()
        
        # Получаем все рецепты, исключая авторские и уже сохраненные
        available_recipes = Recipe.objects.exclude(
            id__in=saved_recipes.values_list('id', flat=True)
        ).exclude(
            author=user
        )
        
        # Если нет доступных рецептов
        if not available_recipes.exists():
            return Response({
                'recommendations': [],
                'type': 'empty',
                'message': 'No recipes available for recommendations',
                'has_recommendations': False
            })
        
        # Если сохраненных рецептов меньше 5 - возвращаем топ залайканные
        if saved_recipes.count() < 5:
            recommended = available_recipes.annotate(
                likes_count=Count('recipelike')
            ).order_by('-likes_count')[:5]
            
            serializer = self.get_serializer(recommended, many=True)
            return Response({
                'recommendations': serializer.data,
                'type': 'popular',
                'message': 'Based on popular recipes',
                'has_recommendations': len(serializer.data) > 0
            })
        
        # Если сохранений 5 и больше - ищем по схожим ингредиентам
        else:
            # Собираем все ингредиенты из сохраненных рецептов
            common_ingredients = Counter()
            for recipe in saved_recipes:
                try:
                    ingredients = json.loads(recipe.ingredients)
                    for ingredient in ingredients:
                        common_ingredients[ingredient.lower()] += 1
                except:
                    ingredients = recipe.ingredients.lower().split(',')
                    for ingredient in ingredients:
                        common_ingredients[ingredient.strip()] += 1
            
            # Получаем топ 10 самых частых ингредиентов
            top_ingredients = [ing for ing, count in common_ingredients.most_common(10)]
            
            # Ищем рецепты с похожими ингредиентами
            recipe_scores = {}
            
            for recipe in available_recipes:
                score = 0
                try:
                    ingredients = json.loads(recipe.ingredients)
                    for ingredient in ingredients:
                        if ingredient.lower() in top_ingredients:
                            score += 1
                except:
                    ingredients = recipe.ingredients.lower().split(',')
                    for ingredient in ingredients:
                        if ingredient.strip() in top_ingredients:
                            score += 1
                
                if score > 0:
                    recipe_scores[recipe.id] = score
            
            # Сортируем по релевантности
            sorted_recipes = sorted(recipe_scores.items(), key=lambda x: x[1], reverse=True)
            recommended_ids = [recipe_id for recipe_id, score in sorted_recipes[:5]]
            
            # Получаем объекты рецептов
            recommended_recipes = Recipe.objects.filter(id__in=recommended_ids).annotate(
                likes_count=Count('recipelike')
            )
            
            # Сортируем в том же порядке
            ordered_recipes = []
            for recipe_id in recommended_ids:
                for recipe in recommended_recipes:
                    if recipe.id == recipe_id:
                        ordered_recipes.append(recipe)
                        break
            
            serializer = self.get_serializer(ordered_recipes, many=True)
            return Response({
                'recommendations': serializer.data,
                'type': 'ingredient_based',
                'message': 'Based on your saved recipes ingredients',
                'common_ingredients': top_ingredients[:5],
                'has_recommendations': len(serializer.data) > 0
            })